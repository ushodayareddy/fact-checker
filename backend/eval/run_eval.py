"""Run the labelled cases in cases.yaml against a live backend and report accuracy.

    cd backend
    uv run python -m eval.run_eval                       # all 50 cases
    uv run python -m eval.run_eval --lang hi --lang ta   # only some languages
    uv run python -m eval.run_eval --id en-01 --id hi-06 # specific cases
    uv run python -m eval.run_eval --limit 5             # smoke run

Outcomes per case:
  pass     verdict is one of the expected labels (or no claims, for `no_claims` cases)
  abstain  verdict was `unverifiable` on a true/false case: unhelpful but not wrong
  fail     verdict contradicts the expectation (the dangerous one: confidently wrong)
  error    the request failed or the pipeline returned an error
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path

import httpx
import yaml

CASES_PATH = Path(__file__).parent / "cases.yaml"
RESULTS_DIR = Path(__file__).parent / "results"


def load_cases(path: Path = CASES_PATH) -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["cases"]


async def parse_sse(lines: AsyncIterator[str]) -> AsyncIterator[tuple[str, str]]:
    """Yield (event, data) from an SSE line stream. Blank line terminates an event."""
    event, data = "message", []
    async for line in lines:
        if line == "":
            if data:
                yield event, "\n".join(data)
            event, data = "message", []
        elif line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].removeprefix(" "))
    if data:
        yield event, "\n".join(data)


def outcome_of(result: dict) -> str:
    verdicts = result.get("verdicts") or []
    return verdicts[0]["label"] if verdicts else "no_claims"


def score(expect: list[str], outcome: str) -> str:
    if outcome in expect:
        return "pass"
    if outcome == "unverifiable" and "no_claims" not in expect:
        return "abstain"
    return "fail"


async def run_case(client: httpx.AsyncClient, case: dict) -> dict:
    row = {"id": case["id"], "lang": case["lang"], "category": case["category"],
           "expect": case["expect"], "text": case["text"]}  # fmt: skip
    start = time.monotonic()
    result, error = None, None
    try:
        async with client.stream("POST", "/api/check", json={"input": case["text"]}) as r:
            if r.status_code != 200:
                error = f"HTTP {r.status_code}"
            else:
                async for event, data in parse_sse(r.aiter_lines()):
                    if event == "result":
                        result = json.loads(data)
                    elif event == "error":
                        error = json.loads(data).get("message", "pipeline error")
    except httpx.HTTPError as e:
        error = f"{type(e).__name__}: {e}"
    row["latency_s"] = round(time.monotonic() - start, 1)

    if error or result is None:
        row.update(status="error", outcome=None, error=error or "no result event")
        return row

    verdict = (result.get("verdicts") or [None])[0]
    outcome = outcome_of(result)
    detected = (result.get("language") or {}).get("code")
    row.update(
        status=score(case["expect"], outcome), outcome=outcome, error=None,
        detected_lang=detected, lang_ok=detected == case["lang"],
        confidence=verdict["confidence"] if verdict else None,
        n_claims=len(result.get("claims") or []),
        n_evidence=sum(len(v) for v in (result.get("evidence") or {}).values()),
        explanation=(verdict or {}).get("explanation", "")[:300],
    )  # fmt: skip
    return row


def summarize(rows: list[dict]) -> dict:
    def tally(group: list[dict]) -> dict:
        c = {s: sum(1 for r in group if r["status"] == s) for s in ("pass", "abstain", "fail", "error")}
        answered = len(group) - c["error"]
        c["total"] = len(group)
        c["accuracy"] = round(c["pass"] / answered, 3) if answered else None
        return c

    by = lambda key: {k: tally([r for r in rows if r[key] == k]) for k in sorted({r[key] for r in rows})}  # noqa: E731
    scored = [r for r in rows if "lang_ok" in r]
    return {
        "overall": tally(rows), "by_language": by("lang"), "by_category": by("category"),
        "language_id_accuracy": round(sum(r["lang_ok"] for r in scored) / len(scored), 3) if scored else None,
    }  # fmt: skip


def print_report(summary: dict, rows: list[dict]) -> None:
    def line(name: str, c: dict) -> str:
        acc = "n/a" if c["accuracy"] is None else f"{c['accuracy']:.0%}"
        return f"{name:<14}{c['total']:>5}{c['pass']:>7}{c['abstain']:>9}{c['fail']:>6}{c['error']:>7}{acc:>10}"

    header = f"{'':<14}{'total':>5}{'pass':>7}{'abstain':>9}{'fail':>6}{'error':>7}{'accuracy':>10}"
    for title, key in (("OVERALL", None), ("BY LANGUAGE", "by_language"), ("BY CATEGORY", "by_category")):
        print(f"\n{title}\n{header}")
        if key is None:
            print(line("all", summary["overall"]))
        else:
            for name, c in summary[key].items():
                print(line(name, c))
    print(f"\nLanguage-ID accuracy: {summary['language_id_accuracy']}")
    bad = [r for r in rows if r["status"] in ("fail", "error")]
    if bad:
        print("\nFAILURES / ERRORS")
        for r in bad:
            what = r["error"] if r["status"] == "error" else f"got {r['outcome']} ({r['confidence']}), expected {r['expect']}"
            print(f"  {r['id']:<8}{r['status']:<7}{what}")


def _cell(text: object) -> str:
    return str(text if text is not None else "").replace("|", "\\|").replace("\n", " ")


def render_markdown(summary: dict, rows: list[dict], meta: dict) -> str:
    """Human-readable report: headline numbers, per-language table, then every non-pass case."""
    ov = summary["overall"]
    acc = "n/a" if ov["accuracy"] is None else f"{ov['accuracy']:.0%}"
    out = [
        "# Fact-checker eval report", "",
        f"- Run: {meta['when']}",
        f"- Models: reasoning `{meta.get('reasoning_model', '?')}`, embedding `{meta.get('embedding_model', '?')}`",
        f"- Cases: {ov['total']}  |  pass {ov['pass']}  |  abstain {ov['abstain']}  |  "
        f"**fail {ov['fail']}**  |  error {ov['error']}  |  accuracy (excluding errors) **{acc}**",
        f"- Language-ID accuracy: {summary['language_id_accuracy']}", "",
        "`fail` means confidently wrong; `abstain` means it said unverifiable. "
        "Non-English claims were AI-translated and not reviewed by native speakers.", "",
    ]  # fmt: skip
    for title, key in (("By language", "by_language"), ("By category", "by_category")):
        out += [f"## {title}", "", "| | total | pass | abstain | fail | error | accuracy |", "|---|---|---|---|---|---|---|"]
        for name, c in summary[key].items():
            a = "n/a" if c["accuracy"] is None else f"{c['accuracy']:.0%}"
            out.append(f"| {name} | {c['total']} | {c['pass']} | {c['abstain']} | {c['fail']} | {c['error']} | {a} |")
        out.append("")
    out += ["## All cases", "", "| id | status | expected | got | conf | evidence | secs | detail |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        detail = r["error"] if r["status"] == "error" else r.get("explanation", "")
        out.append(
            f"| {r['id']} | {r['status']} | {_cell(','.join(r['expect']))} | {_cell(r.get('outcome'))} | "
            f"{_cell(r.get('confidence'))} | {_cell(r.get('n_evidence'))} | {r['latency_s']} | {_cell(detail)[:200]} |"
        )  # fmt: skip
    bad = [r for r in rows if r["status"] in ("fail", "error")]
    if bad:
        out += ["", "## Failures and errors (claim text)", ""]
        out += [f"- **{r['id']}** ({r['lang']}, {r['status']}): {r['text']}" for r in bad]
    return "\n".join(out) + "\n"


async def main_async(args: argparse.Namespace) -> int:
    cases = load_cases()
    if args.id:
        cases = [c for c in cases if c["id"] in args.id]
    if args.lang:
        cases = [c for c in cases if c["lang"] in args.lang]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print("No cases matched the filters.", file=sys.stderr)
        return 2

    timeout = httpx.Timeout(args.timeout, connect=5.0)
    async with httpx.AsyncClient(base_url=args.base_url, timeout=timeout) as client:
        try:
            health = (await client.get("/api/health")).json()
        except httpx.HTTPError as e:
            print(f"Cannot reach backend at {args.base_url}: {e}\nStart it first (see README).", file=sys.stderr)
            return 2
        if not health.get("ok"):
            print(f"Backend is up but not ready: {health}. Run `ollama serve` and pull the missing models.", file=sys.stderr)
            return 2

        sem = asyncio.Semaphore(args.concurrency)
        rows: list[dict] = []

        async def one(case: dict) -> None:
            async with sem:
                row = await run_case(client, case)
            rows.append(row)
            print(f"[{len(rows):>2}/{len(cases)}] {row['id']:<7}{row['status']:<8}{row.get('outcome')}  ({row['latency_s']}s)", flush=True)

        await asyncio.gather(*(one(c) for c in cases))

    rows.sort(key=lambda r: [c["id"] for c in cases].index(r["id"]))
    summary = summarize(rows)
    print_report(summary, rows)

    RESULTS_DIR.mkdir(exist_ok=True)
    out = Path(args.out) if args.out else RESULTS_DIR / f"eval-{datetime.now():%Y%m%d-%H%M%S}.json"
    payload = json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2)
    meta = {"when": f"{datetime.now():%Y-%m-%d %H:%M}", **health.get("models", {})}
    markdown = render_markdown(summary, rows, meta)
    out.write_text(payload, encoding="utf-8")
    out.with_suffix(".md").write_text(markdown, encoding="utf-8")
    # Fixed names so a person (or eval.bat) always knows where the newest report is.
    (RESULTS_DIR / "latest.json").write_text(payload, encoding="utf-8")
    (RESULTS_DIR / "latest.md").write_text(markdown, encoding="utf-8")
    print(f"\nWrote {out} and {out.with_suffix('.md')} (copies: latest.json, latest.md)")

    acc = summary["overall"]["accuracy"]
    if args.min_accuracy is not None and (acc is None or acc < args.min_accuracy):
        print(f"Accuracy {acc} is below the required {args.min_accuracy}.", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--lang", action="append", help="only this language code (repeatable)")
    p.add_argument("--id", action="append", help="only this case id (repeatable)")
    p.add_argument("--limit", type=int, help="run only the first N matching cases")
    p.add_argument("--concurrency", type=int, default=1, help="parallel cases; local models serialise, keep at 1-2")
    p.add_argument("--timeout", type=float, default=600.0, help="per-request seconds")
    p.add_argument("--out", help="JSON report path (default: eval/results/eval-<timestamp>.json)")
    p.add_argument("--min-accuracy", type=float, help="exit 1 if accuracy is below this (0-1)")
    sys.exit(asyncio.run(main_async(p.parse_args())))


if __name__ == "__main__":
    main()
