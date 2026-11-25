"""Diagrams and the optional results chart, drawn at the size they will appear in each document.

Layouts are defined in abstract units and scaled to the requested width, so text stays legible
whether the figure lands in a 3.4in IEEE column, an A4 report page or a 16:9 slide.

Colour: the two-tone scheme (blue = generative LLM involved, neutral = plain code) is always paired
with a text tag, never colour alone. Values are from the dataviz skill's reference palette.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans"]

INK, SEC, MUTED = "#0b0b0b", "#52514e", "#898781"
BLUE, BLUE_FILL, NEUTRAL_FILL, RULE = "#2a78d6", "#cde2fb", "#eceae5", "#c3c2b7"
WHITE = "#ffffff"


def _canvas(w_in: float, units_w: float, units_h: float):
    fig = plt.figure(figsize=(w_in, w_in * units_h / units_w), dpi=300, facecolor=WHITE)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, units_w)
    ax.set_ylim(0, units_h)
    ax.axis("off")
    return fig, ax, w_in / units_w


def _box(ax, cx, cy, w, h, fill=WHITE, edge=BLUE, lw=1.0, dashed=False):
    ax.add_patch(
        FancyBboxPatch(
            (cx - w / 2, cy - h / 2), w, h, boxstyle="round,pad=0,rounding_size=0.12",
            fc=fill, ec=edge, lw=lw, ls="--" if dashed else "-",
        )
    )  # fmt: skip


def _text(ax, x, y, s, fs, weight="normal", color=INK, ha="center", va="center", style="normal", ls=1.2):
    ax.text(x, y, s, fontsize=fs, fontweight=weight, color=color, ha=ha, va=va, fontstyle=style, linespacing=ls)


def _arrow(ax, p0, p1, color=SEC, lw=1.0):
    ax.annotate(
        "", xy=p1, xytext=p0,
        arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, shrinkA=0, shrinkB=0, mutation_scale=7),
    )  # fmt: skip


AGENTS_WIDE = [
    ("1  Claim Extractor", "atomic claims, EN gloss", True),
    ("2  Language ID", "script + lingua, tier", False),
    ("3  Claim Router", "rules, LLM fallback", True),
    ("4  Evidence Retriever", "parallel adapters, rerank", False),
    ("5  Source Validator", "domain tier, recency", False),
    ("6  Claim Verifier", "stance + exact quote", True),
    ("7  Verdict Synthesizer", "rules score; LLM explains", True),
]


def architecture(path: Path, kind: str = "wide", w_in: float = 6.3) -> Path:
    """Pipeline diagram. kind='wide' (two snaking rows) or 'tall' (one column, for an IEEE column)."""
    if kind == "wide":
        fig, ax, k = _canvas(w_in, 12, 6.4)
        tfs, sfs, bw, bh = 14.5 * k, 11.5 * k, 2.5, 1.1
        xs = [1.45, 4.3, 7.15, 10.0]
        pos = [(xs[0], 5.15), (xs[1], 5.15), (xs[2], 5.15), (xs[3], 5.15),
               (xs[3], 3.1), (xs[2], 3.1), (xs[1], 3.1), (xs[0], 3.1)]  # fmt: skip
        # input box then agents 1..3 on row A; agents 4..7 on row B (right to left)
        _box(ax, xs[0], 5.15, 2.2, 0.9, NEUTRAL_FILL, SEC)
        _text(ax, xs[0], 5.15, "Claim text\nor article URL", tfs * 0.95, "bold", ls=1.15)
        agent_pos = [(xs[1], 5.15), (xs[2], 5.15), (xs[3], 5.15), (xs[3], 3.1), (xs[2], 3.1), (xs[1], 3.1), (xs[0], 3.1)]
        for (title, sub, llm), (x, y) in zip(AGENTS_WIDE, agent_pos):
            _box(ax, x, y, bw, bh, BLUE_FILL if llm else NEUTRAL_FILL, BLUE if llm else SEC)
            _text(ax, x, y + 0.2, title, tfs, "bold")
            _text(ax, x, y - 0.25, sub, sfs, color=SEC)
        _arrow(ax, (xs[0] + 1.1, 5.15), (xs[1] - bw / 2, 5.15))
        for a, b in [(0, 1), (1, 2)]:
            _arrow(ax, (agent_pos[a][0] + bw / 2, 5.15), (agent_pos[b][0] - bw / 2, 5.15))
        _arrow(ax, (xs[3], 5.15 - bh / 2), (xs[3], 3.1 + bh / 2))  # 3 -> 4
        for a, b in [(3, 4), (4, 5), (5, 6)]:
            _arrow(ax, (agent_pos[a][0] - bw / 2, 3.1), (agent_pos[b][0] + bw / 2, 3.1))
        # output
        _box(ax, xs[0], 1.0, 2.5, 0.95, NEUTRAL_FILL, SEC)
        _text(ax, xs[0], 1.0, "Verdict, evidence\nand live trace (SSE)", tfs * 0.95, "bold", ls=1.15)
        _arrow(ax, (xs[0], 3.1 - bh / 2), (xs[0], 1.0 + 0.475))
        # sources panel
        _box(ax, 8.55, 1.0, 5.4, 1.15, WHITE, SEC, dashed=True)
        _text(ax, 8.55, 1.32, "Evidence sources, chosen by claim type", sfs * 1.05, "bold")
        _text(ax, 8.55, 0.92, "Wikipedia  ·  Wikidata  ·  government sites", sfs, color=SEC)
        _text(ax, 8.55, 0.6, "fact-check archives  ·  web search", sfs, color=SEC)
        _arrow(ax, (xs[3], 1.575), (xs[3], 3.1 - bh / 2))
        # legend
        for y, fill, edge, label in [(1.25, BLUE_FILL, BLUE, "generative LLM involved"), (0.7, NEUTRAL_FILL, SEC, "no generative LLM")]:
            _box(ax, 3.4, y, 0.32, 0.26, fill, edge)
            _text(ax, 3.7, y, label, sfs, color=SEC, ha="left")
    else:  # tall
        fig, ax, k = _canvas(w_in, 6, 9.4)
        tfs, sfs, bw, bh = 12.5 * k, 10.2 * k, 3.3, 0.78
        cx = 1.95
        _box(ax, cx, 8.9, 2.4, 0.55, NEUTRAL_FILL, SEC)
        _text(ax, cx, 8.9, "Claim text or article URL", tfs * 0.85, "bold")
        ys = [7.85 - i * 1.0 for i in range(7)]
        for (title, sub, llm), y in zip(AGENTS_WIDE, ys):
            _box(ax, cx, y, bw, bh, BLUE_FILL if llm else NEUTRAL_FILL, BLUE if llm else SEC)
            _text(ax, cx, y + 0.15, title, tfs, "bold")
            _text(ax, cx, y - 0.2, sub, sfs, color=SEC)
        _arrow(ax, (cx, 8.9 - 0.275), (cx, ys[0] + bh / 2))
        for a, b in zip(ys, ys[1:]):
            _arrow(ax, (cx, a - bh / 2), (cx, b + bh / 2))
        _box(ax, cx, 0.6, bw, 0.72, NEUTRAL_FILL, SEC)
        _text(ax, cx, 0.6, "Verdict, evidence, live trace", tfs * 0.9, "bold")
        _arrow(ax, (cx, ys[-1] - bh / 2), (cx, 0.6 + 0.36))
        # sources panel (right of retriever)
        _box(ax, 4.95, ys[3], 1.9, 2.15, WHITE, SEC, dashed=True)
        _text(ax, 4.95, ys[3] + 0.8, "Sources", sfs * 1.05, "bold")
        for i, s in enumerate(["Wikipedia", "Wikidata", "govt sites", "fact-check", "web search"]):
            _text(ax, 4.95, ys[3] + 0.42 - i * 0.3, s, sfs, color=SEC)
        _arrow(ax, (4.0, ys[3]), (cx + bw / 2, ys[3]))
        for y, fill, edge, label in [(2.1, BLUE_FILL, BLUE, "LLM involved"), (1.6, NEUTRAL_FILL, SEC, "no LLM")]:
            _box(ax, 4.25, y, 0.28, 0.24, fill, edge)
            _text(ax, 4.5, y, label, sfs, color=SEC, ha="left")
    fig.savefig(path, dpi=300, facecolor=WHITE)
    plt.close(fig)
    return path


def verdict_flow(path: Path, w_in: float = 3.45) -> Path:
    """Decision flow that turns credibility-weighted stances into a verdict label."""
    fig, ax, k = _canvas(w_in, 7.4, 9.0)
    fs, sfs = 14 * k, 11.5 * k
    mx, sx, dw, dh = 1.9, 5.55, 3.3, 0.9
    gap_mid = (mx + dw / 2 + (sx - 1.3)) / 2  # centre of the gap between left column and right boxes

    def decision(cx, cy, text, w=dw):
        _box(ax, cx, cy, w, dh, BLUE_FILL, BLUE, lw=1.3)
        _text(ax, cx, cy, text, fs * 0.95, "bold", ls=1.15)

    def outcome(cx, cy, text, w=2.6, h=0.7, dashed=False):
        _box(ax, cx, cy, w, h, WHITE, SEC, lw=1.2, dashed=dashed)
        _text(ax, cx, cy, text, fs * 0.95, "bold", ls=1.15)

    _box(ax, mx, 8.4, dw, 0.8, NEUTRAL_FILL, SEC)
    _text(ax, mx, 8.4, "stance x credibility\n= W_sup, W_ref", fs * 0.95, "bold", ls=1.15)
    decision(mx, 6.9, "W_sup + W_ref\n< 0.5 ?")
    outcome(sx, 6.9, "Unverifiable\n(no credible evidence)")
    decision(mx, 5.3, "both sides hold\n>= 25 % of weight?")
    decision(sx, 5.3, "a fact-checker\namong refuters?", w=2.6)
    outcome(4.7, 3.95, "Misleading", w=1.5, h=0.6)
    outcome(6.4, 3.95, "Partly true", w=1.5, h=0.6)
    decision(mx, 2.6, "winning side's\nweight >= 0.7 ?")
    outcome(sx, 2.6, "Unverifiable\n(thin evidence)")
    outcome(mx, 1.35, "True  /  False", w=2.4, h=0.65)
    # note
    _box(ax, 3.7, 0.4, 7.0, 0.62, WHITE, MUTED, dashed=True, lw=0.9)
    _text(ax, 3.7, 0.4, "confidence capped by language tier: 0.95 / 0.80 / 0.60", sfs, color=SEC)
    # arrows and labels
    _arrow(ax, (mx, 8.4 - 0.4), (mx, 6.9 + dh / 2))
    _arrow(ax, (mx + dw / 2, 6.9), (sx - 1.3, 6.9))
    _text(ax, gap_mid, 7.22, "yes", sfs, color=SEC)
    _arrow(ax, (mx, 6.9 - dh / 2), (mx, 5.3 + dh / 2))
    _text(ax, mx + 0.3, 6.1, "no", sfs, color=SEC, ha="left")
    _arrow(ax, (mx + dw / 2, 5.3), (sx - 1.3, 5.3))
    _text(ax, gap_mid, 5.62, "yes", sfs, color=SEC)
    _arrow(ax, (sx - 0.6, 5.3 - dh / 2), (4.7, 3.95 + 0.3))
    _text(ax, 4.15, 4.62, "yes", sfs, color=SEC)
    _arrow(ax, (sx + 0.6, 5.3 - dh / 2), (6.4, 3.95 + 0.3))
    _text(ax, 6.8, 4.62, "no", sfs, color=SEC)
    _arrow(ax, (mx, 5.3 - dh / 2), (mx, 2.6 + dh / 2))
    _text(ax, mx + 0.3, 3.95, "no", sfs, color=SEC, ha="left")
    _arrow(ax, (mx + dw / 2, 2.6), (sx - 1.3, 2.6))
    _text(ax, gap_mid, 2.92, "no", sfs, color=SEC)
    _arrow(ax, (mx, 2.6 - dh / 2), (mx, 1.35 + 0.325))
    _text(ax, mx + 0.3, 1.95, "yes", sfs, color=SEC, ha="left")
    fig.savefig(path, dpi=300, facecolor=WHITE)
    plt.close(fig)
    return path


def accuracy_by_language(path: Path, by_language: dict, w_in: float = 6.0) -> Path | None:
    """Single-series horizontal bars of accuracy per language, drawn only from real eval results."""
    rows = [(lang, c["accuracy"], c["total"]) for lang, c in by_language.items() if c.get("accuracy") is not None]
    if not rows:
        return None
    rows.sort(key=lambda r: (-r[1], r[0]))
    h_in = max(2.0, 0.34 * len(rows) + 0.9)
    fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=300, facecolor=WHITE)
    labels = [f"{lang}  (n={n})" for lang, _, n in rows]
    vals = [a * 100 for _, a, _ in rows]
    ypos = list(range(len(rows)))[::-1]
    ax.barh(ypos, vals, height=0.55, color=BLUE)
    ax.set_yticks(ypos, labels, fontsize=8, color=INK)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Accuracy, % of answered cases (errors excluded)", fontsize=8, color=SEC)
    ax.tick_params(axis="x", labelsize=8, colors=MUTED, length=0)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color="#e1e0d9", lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(RULE)
    for y, v in zip(ypos, vals):
        ax.text(min(v + 1.5, 97), y, f"{v:.0f}%", va="center", fontsize=8, color=INK)
    fig.tight_layout()
    fig.savefig(path, dpi=300, facecolor=WHITE)
    plt.close(fig)
    return path


def build_all(out_dir: Path, results: dict | None = None) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    figs = {
        "arch_wide": architecture(out_dir / "architecture_wide.png", "wide", 6.3),
        "arch_slide": architecture(out_dir / "architecture_slide.png", "wide", 12.0),
        "arch_tall": architecture(out_dir / "architecture_tall.png", "tall", 3.4),
        "flow_report": verdict_flow(out_dir / "verdict_flow_report.png", 4.6),
        "flow_paper": verdict_flow(out_dir / "verdict_flow_paper.png", 3.45),
        "flow_slide": verdict_flow(out_dir / "verdict_flow_slide.png", 5.6),
    }
    if results:
        p = accuracy_by_language(out_dir / "accuracy_by_language.png", results["summary"]["by_language"])
        if p:
            figs["accuracy"] = p
    return figs


if __name__ == "__main__":
    import sys

    for name, p in build_all(Path(sys.argv[1] if len(sys.argv) > 1 else "../figures")).items():
        print(name, p)
