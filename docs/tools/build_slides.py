"""Build the project presentation (.pptx), 16:9, with speaker notes.

One idea per slide, a headline that states the claim, and figures instead of walls of text. Detail lives in the
speaker notes so the presenter can talk from them. Where results do not exist the results slide says so plainly.
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

import content as C
from facts import results_sentence

INK, SEC, MUTED = RGBColor(0x0B, 0x0B, 0x0B), RGBColor(0x52, 0x51, 0x4E), RGBColor(0x89, 0x87, 0x81)
BLUE, BLUE_FILL, RULE, SURFACE = RGBColor(0x2A, 0x78, 0xD6), RGBColor(0xCD, 0xE2, 0xFB), RGBColor(0xC3, 0xC2, 0xB7), RGBColor(0xFC, 0xFC, 0xFB)
NAVY = RGBColor(0x0D, 0x36, 0x6B)
FONT = "Calibri"
SW, SH = Inches(13.333), Inches(7.5)
MX = Inches(0.7)


class Deck:
    def __init__(self, facts, team, results, fig_dir):
        self.f, self.t, self.res, self.fig = facts, team, results, fig_dir
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = SW, SH
        self.blank = self.prs.slide_layouts[6]
        self.missing: list[str] = []
        self.n = 0

    # --- primitives ---
    def slide(self, notes: str = ""):
        s = self.prs.slides.add_slide(self.blank)
        self.n += 1
        bg = s.background.fill
        bg.solid()
        bg.fore_color.rgb = SURFACE
        if notes:
            s.notes_slide.notes_text_frame.text = notes
        return s

    def text(self, s, x, y, w, h, text, size=18, bold=False, color=INK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, italic=False):
        tb = s.shapes.add_textbox(x, y, w, h)
        tf = tb.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        tf.margin_left = tf.margin_right = Inches(0.05)
        tf.margin_top = tf.margin_bottom = Inches(0.03)
        lines = text if isinstance(text, list) else [text]
        for i, ln in enumerate(lines):
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            para.alignment = align
            r = para.add_run()
            r.text = ln
            r.font.name, r.font.size, r.font.bold, r.font.italic = FONT, Pt(size), bold, italic
            r.font.color.rgb = color
        return tb

    def title(self, s, text, kicker=None):
        if kicker:
            self.text(s, MX, Inches(0.35), Inches(11), Inches(0.35), kicker.upper(), 13, True, BLUE)
        self.text(s, MX, Inches(0.68), SW - 2 * MX, Inches(1.1), text, 30, True, INK, anchor=MSO_ANCHOR.TOP)

    def footer(self, s):
        self.text(s, MX, Inches(7.02), Inches(9), Inches(0.3), "Agentic Fact-Checking for Indian Languages", 11, False, MUTED)
        self.text(s, SW - MX - Inches(1), Inches(7.02), Inches(1), Inches(0.3), str(self.n), 11, False, MUTED, PP_ALIGN.RIGHT)

    def bullets(self, s, items, x, y, w, size=20, gap=0.14, color=INK):
        # size the box to its content so layout checks (and PowerPoint's selection box) match what is drawn
        cpl = max(1, int((w / 914400 - 0.1) * 72 / (size * 0.52)))
        est = sum(max(1, -(-(len(i) + 3) // cpl)) * size * 1.2 / 72 + gap for i in items)
        tb = s.shapes.add_textbox(x, y, w, Inches(est + 0.1))
        tf = tb.text_frame
        tf.word_wrap = True
        for i, it in enumerate(items):
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            para.space_after = Pt(gap * 72)
            r = para.add_run()
            r.text = "•  " + it
            r.font.name, r.font.size = FONT, Pt(size)
            r.font.color.rgb = color
        return tb

    def card(self, s, x, y, w, h, head, body, fill=BLUE_FILL, edge=BLUE):
        shp = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
        shp.adjustments[0] = 0.06
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
        shp.line.color.rgb = edge
        shp.line.width = Pt(1.25)
        shp.shadow.inherit = False
        self.text(s, x + Inches(0.15), y + Inches(0.1), w - Inches(0.3), Inches(0.5), head, 18, True, INK)
        self.text(s, x + Inches(0.15), y + Inches(0.62), w - Inches(0.3), h - Inches(0.7), body, 15, False, SEC)

    def picture(self, s, path: Path, x, y, max_w, max_h):
        from PIL import Image

        w, h = Image.open(path).size
        scale = min(max_w / w, max_h / h)
        pw, ph = int(w * scale), int(h * scale)
        s.shapes.add_picture(str(path), x + int((max_w - pw) / 2), y + int((max_h - ph) / 2), pw, ph)

    # --- slides ---
    def build(self):
        f, t, m = self.f, self.t, self.missing
        thr = f["thresholds"]

        # 1 title
        s = self.slide("Introduce the project and the team. State the one-sentence pitch: check claims in any Indian language, on a local machine, with every verdict traceable to a quoted source.")
        logo = self.fig / "jain_logo.png"
        if logo.exists():
            s.shapes.add_picture(str(logo), MX, Inches(0.5), height=Inches(0.8))
        self.text(s, MX, Inches(1.9), Inches(11.5), Inches(2.2), t["project_title"], 34, True, INK)
        names = [x["name"].strip() or f"[Student {i + 1}]" for i, x in enumerate(t["team"])]
        for i, x in enumerate(t["team"]):
            if not x["name"].strip():
                m.append(f"Student {i + 1} name")
        guide = t["guide"]["name"].strip() or "[Guide name]"
        if not t["guide"]["name"].strip():
            m.append("Guide name")
        self.text(s, MX, Inches(4.5), Inches(11.5), Inches(0.5), "  ·  ".join(names), 20, True, SEC)
        self.text(s, MX, Inches(5.05), Inches(11.5), Inches(0.4), f"Guide: {guide}", 18, False, SEC)
        self.text(s, MX, Inches(6.0), Inches(11.5), Inches(0.8), ["Department of Computer Science & Engineering - AIML", "Faculty of Engineering & Technology, JAIN (Deemed-to-be University)"], 14, False, MUTED)

        # 2 problem
        s = self.slide(
            "Misinformation in India moves in many languages at once. Fact-checks exist, but a reader in Tamil or Odia usually cannot find out whether a claim was checked, "
            "and cannot judge whether the source they found is trustworthy. Most research is English-only and most tools need a hosted model."
        )
        self.title(s, "A claim in Tamil or Odia is hard to check, and harder to trust", "The problem")
        cw = Inches(3.75)
        gap = Inches(0.3)
        y = Inches(2.2)
        self.card(s, MX, y, cw, Inches(2.9), "Many languages", f"{f['n_languages'] - 1} scheduled languages. Fact-checkers are few and indexed content in most of them is thin.")
        self.card(s, MX + cw + gap, y, cw, Inches(2.9), "Unknown trust", "A reader cannot tell a government page from a forwarded blog, or whether the claim was already debunked.")
        self.card(s, MX + 2 * (cw + gap), y, cw, Inches(2.9), "Closed tools", "Most research targets English; deployed checkers lean on hosted models that send each claim off the machine.")
        self.text(s, MX, Inches(5.5), SW - 2 * MX, Inches(1), "Goal: take a claim in any scheduled Indian language, find evidence, judge how far each source can be trusted, and answer in the user's language.", 20, True, SEC)
        self.footer(s)

        # 3 gap
        s = self.slide(
            "Walk the table left to right. FEVER, MultiFC, AVeriTeC are English. X-FACT is multilingual and the Indian resources exist, but they are datasets and classifiers. "
            "RAG and ReAct give the retrieve-then-reason pattern but no source-reliability policy. Say clearly this survey is limited to the papers shown and does not claim no other system exists."
        )
        self.title(s, "Existing work gives datasets and methods, not a system that weighs sources", "Related work")
        rows = [
            ("FEVER, MultiFC, AVeriTeC", "English claims and evidence", "No Indian languages"),
            ("X-FACT", "Statements in 25 languages", "Classifier; no retrieval or source validation"),
            ("FactDRIL, claim matching", "Indian fact-check data; Hindi, Bengali, Tamil and more", "Resources, not a verifier"),
            ("RAG, ReAct", "Ground a model in retrieved text", "No source-reliability policy"),
        ]
        ty = Inches(2.2)
        self.text(s, MX, ty, Inches(3.6), Inches(0.4), "Work", 15, True, MUTED)
        self.text(s, MX + Inches(3.8), ty, Inches(4), Inches(0.4), "What it offers", 15, True, MUTED)
        self.text(s, MX + Inches(7.9), ty, Inches(4), Inches(0.4), "Gap for this problem", 15, True, MUTED)
        for i, (a, b, c) in enumerate(rows):
            yy = ty + Inches(0.55) + Inches(0.88) * i
            ln = s.shapes.add_connector(1, MX, yy - Inches(0.06), SW - MX, yy - Inches(0.06))
            ln.line.color.rgb = RULE
            ln.line.width = Pt(0.75)
            self.text(s, MX, yy, Inches(3.7), Inches(0.8), a, 18, True)
            self.text(s, MX + Inches(3.8), yy, Inches(4), Inches(0.8), b, 17, False, SEC)
            self.text(s, MX + Inches(7.9), yy, Inches(4.7), Inches(0.8), c, 17, False, SEC)
        self.footer(s)

        # 4 approach
        s = self.slide(
            "Three decisions define the work. First, seven narrow agents instead of one big prompt, so each step can be tested. Second, a stance only counts if the model quotes the evidence. "
            "Third, the verdict label is computed by rules; the language model only explains it. That makes results reproducible and auditable."
        )
        self.title(s, "Three decisions make the verdicts auditable", "Approach")
        for i, (h, b) in enumerate([
            ("Seven narrow agents", "Extract, identify language, route, retrieve, validate, verify, synthesise. Each step is separately testable."),
            ("Quote or discard", "A supports/refutes stance is kept only if its quote appears in the evidence. Invented justifications are dropped."),
            ("Rules decide, model explains", "The label and confidence are computed from credibility-weighted stances. The model writes the explanation."),
        ]):
            self.card(s, MX + i * (cw + gap), Inches(2.2), cw, Inches(3.0), f"{i + 1}.  {h}", b)
        self.text(s, MX, Inches(5.6), SW - 2 * MX, Inches(1), "Everything runs locally through Ollama: no claim leaves the machine and there is no per-query fee.", 20, True, SEC)
        self.footer(s)

        # 5 architecture
        s = self.slide(
            "Follow the arrows. Blue boxes use the language model; grey boxes are ordinary code, which is most of the pipeline. "
            "Retrieval fans out to the sources chosen for the claim type. The trace of each step streams to the interface so users watch progress during the slow local-model calls."
        )
        self.title(s, "Seven agents share one state and stream their progress", "Architecture")
        self.picture(s, self.fig / "architecture_slide.png", MX, Inches(1.85), SW - 2 * MX, Inches(5.0))
        self.footer(s)

        # 6 routing + sources
        s = self.slide(
            "Different claims need different evidence. A budget figure belongs to government sources, a WhatsApp rumour to fact-check archives, a landmark to an encyclopaedia. "
            "Queries run in the claim's language and in English, because Indian-language content is thin online. A failing source is skipped, not fatal."
        )
        self.title(s, "The claim's type decides where evidence is sought", "Routing")
        names = {"statistical": "Statistics and policy", "viral": "Viral rumour", "entity": "People, places, events", "breaking": "Breaking news", "health": "Health and science"}
        y0 = Inches(2.2)
        self.text(s, MX, y0, Inches(3.5), Inches(0.4), "Claim type", 15, True, MUTED)
        self.text(s, MX + Inches(3.7), y0, Inches(8), Inches(0.4), "Sources, in order", 15, True, MUTED)
        for i, (k, v) in enumerate(C.routing_rows(f)):
            yy = y0 + Inches(0.55) + Inches(0.78) * i
            ln = s.shapes.add_connector(1, MX, yy - Inches(0.06), SW - MX, yy - Inches(0.06))
            ln.line.color.rgb = RULE
            ln.line.width = Pt(0.75)
            self.text(s, MX, yy, Inches(3.6), Inches(0.7), names.get(k, k), 19, True)
            self.text(s, MX + Inches(3.7), yy, Inches(8.5), Inches(0.7), v, 19, False, SEC)
        self.footer(s)

        # 7 credibility
        s = self.slide(
            "Each source starts from a prior by domain tier, then loses points for age and low relevance. Every adjustment is recorded as a reason and shown on hover. "
            "Be upfront that this registry is a hand-written prior and should be reviewed by domain experts."
        )
        self.title(s, "Every source gets a credibility score, with reasons", "Source validation")
        tiers = list(f["source_tiers"].items())
        bx, by, bw = MX, Inches(2.2), Inches(5.8)
        for i, (k, v) in enumerate(tiers):
            yy = by + Inches(0.62) * i
            self.text(s, bx, yy, Inches(2.9), Inches(0.5), k.replace("_", " ").capitalize(), 17, False, INK)
            track = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, bx + Inches(3.0), yy + Inches(0.12), Inches(2.0), Inches(0.26))
            track.fill.solid(); track.fill.fore_color.rgb = RGBColor(0xEC, 0xEA, 0xE5); track.line.fill.background(); track.shadow.inherit = False
            fillw = int(Inches(2.0) * v["credibility"])
            bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, bx + Inches(3.0), yy + Inches(0.12), fillw, Inches(0.26))
            bar.fill.solid(); bar.fill.fore_color.rgb = BLUE; bar.line.fill.background(); bar.shadow.inherit = False
            self.text(s, bx + Inches(5.05), yy, Inches(0.8), Inches(0.5), f"{v['credibility']:.2f}", 17, True, INK)
        self.text(s, Inches(7.4), Inches(2.2), Inches(5.2), Inches(0.4), "Then adjusted for", 17, True, MUTED)
        self.bullets(s, ["Age: over 3 years loses 0.03 a year, up to 0.15", "No publication date on a news or unknown source: −0.03", "Low relevance to the claim: −0.10", "Each reason is stored and shown to the user"], Inches(7.4), Inches(2.7), Inches(5.3), 18)
        self.footer(s)

        # 8 quote grounding
        s = self.slide(
            "This is the guard against a specific failure: a model that says 'refutes' and quotes a sentence the page never contained. "
            "We normalise case and whitespace and search for the quote in the evidence. No match means the stance is replaced by neutral."
        )
        self.title(s, "A judgement without a verifiable quote is discarded", "Claim verification")
        self.card(s, MX, Inches(2.2), Inches(5.7), Inches(2.4), "Model says", "“Refutes.  Quote: ‘Delhi was never the capital.’”", RGBColor(0xEC, 0xEA, 0xE5), SEC)
        self.card(s, Inches(6.9), Inches(2.2), Inches(5.7), Inches(2.4), "Evidence actually says", "“New Delhi is the capital of India.”", RGBColor(0xEC, 0xEA, 0xE5), SEC)
        arrow = s.shapes.add_shape(MSO_SHAPE.DOWN_ARROW, Inches(6.35), Inches(4.8), Inches(0.6), Inches(0.7))
        arrow.fill.solid(); arrow.fill.fore_color.rgb = BLUE; arrow.line.fill.background(); arrow.shadow.inherit = False
        self.text(s, MX, Inches(5.65), SW - 2 * MX, Inches(1.0), "Quote not found in the evidence → stance becomes neutral. It adds no weight to the verdict.", 22, True, INK, PP_ALIGN.CENTER)
        self.footer(s)

        # 9 verdict policy
        s = self.slide(
            "The label comes from weights, not from the model. If total weight is under 0.5 we say unverifiable. "
            "If both sides hold at least a quarter of the weight the sources disagree: misleading if a fact-checker refutes, partly true otherwise. "
            f"Otherwise one side must carry weight of at least {thr['min_decisive']} to give true or false. Confidence is capped by language tier at {thr['cap']['high']}, {thr['cap']['medium']} and {thr['cap']['low']}. "
            "These thresholds are conservative and have not been tuned on data."
        )
        self.title(s, "The verdict is computed by rules, then explained by the model", "Verdict policy")
        self.picture(s, self.fig / "verdict_flow_slide.png", MX, Inches(1.85), Inches(6.4), Inches(5.05))
        self.bullets(
            s,
            ["Weights are summed credibility of supporting and refuting sources", f"Below {thr['min_total']} total weight: unverifiable, zero confidence", "Sources disagree: misleading or partly true, both sides cited",
             f"Confidence capped by language tier: {thr['cap']['high']} / {thr['cap']['medium']} / {thr['cap']['low']}"],
            Inches(7.5), Inches(2.1), Inches(5.2), 19,
        )
        self.footer(s)

        # 10 languages
        s = self.slide(
            "All 22 scheduled languages plus English are supported by design. Local models and retrieval are weaker in the low-resource ones, so we do not hide it: "
            "the interface warns the user and confidence is capped. Be honest that the language detector cannot yet separate some languages that share a script."
        )
        self.title(s, "Weak languages are flagged and their confidence is capped", "Language coverage")
        cols = [("high", "High", f"{thr['cap']['high']:.2f}"), ("medium", "Medium", f"{thr['cap']['medium']:.2f}"), ("low", "Low", f"{thr['cap']['low']:.2f}")]
        for i, (k, label, cap) in enumerate(cols):
            x = MX + i * (cw + gap)
            names_ = ", ".join(l.name for l in f["tiers"][k])
            shp = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, Inches(2.2), cw, Inches(3.5))
            shp.adjustments[0] = 0.05
            shp.fill.solid(); shp.fill.fore_color.rgb = BLUE_FILL if k != "low" else RGBColor(0xEC, 0xEA, 0xE5)
            shp.line.color.rgb = BLUE if k != "low" else SEC; shp.line.width = Pt(1.25); shp.shadow.inherit = False
            self.text(s, x + Inches(0.15), Inches(2.3), cw - Inches(0.3), Inches(0.5), f"{label} resource  ·  confidence ≤ {cap}", 17, True)
            self.text(s, x + Inches(0.15), Inches(2.9), cw - Inches(0.3), Inches(2.7), names_, 15, False, SEC)
        self.text(s, MX, Inches(6.0), SW - 2 * MX, Inches(0.9), "Known gap: a correct Marathi sentence in our test set is identified as Hindi (score 0.53 vs 0.47).", 18, True, INK)
        self.footer(s)

        # 11 implementation
        s = self.slide("Brief stack slide. Emphasise: Python and FastAPI backend, React front end, local models through Ollama, schema-constrained JSON with retries, and Windows scripts for setup, run and evaluation.")
        self.title(s, "A single-machine stack: FastAPI, React and local models", "Implementation")
        rows = C.implementation_rows(f)[:7]
        for i, (a, b) in enumerate(rows):
            yy = Inches(2.1) + Inches(0.66) * i
            ln = s.shapes.add_connector(1, MX, yy - Inches(0.05), SW - MX, yy - Inches(0.05))
            ln.line.color.rgb = RULE; ln.line.width = Pt(0.75)
            self.text(s, MX, yy, Inches(2.6), Inches(0.6), a, 16, True)
            self.text(s, MX + Inches(2.7), yy, Inches(9.2), Inches(0.62), b if len(b) < 150 else b[:147] + "…", 14, False, SEC)
        self.footer(s)

        # 12 testing
        tf = f["tests"]
        s = self.slide(
            f"{tf['passed']} automated tests pass with {tf['xfailed']} expected failure. They use scripted model replies and recorded response shapes, so they verify logic and failure handling, "
            "not model quality or live-source behaviour. The expected failure is the Marathi language-ID gap, kept visible on purpose."
        )
        self.title(s, f"{tf['passed']} tests verify the logic, not the model quality", "Testing")
        self.text(s, MX, Inches(2.1), Inches(4.3), Inches(1.4), str(tf["passed"]), 88, True, BLUE)
        self.text(s, MX, Inches(3.75), Inches(4.3), Inches(0.9), f"passing tests, {tf['xfailed']} expected failure", 20, False, SEC)
        self.bullets(
            s,
            ["Every verdict branch and the confidence cap", "Fabricated quotes are rejected", "A failing source or model degrades safely", "Spoofed look-alike domains do not match a trusted tier", "Evaluation dataset integrity and scoring"],
            Inches(5.4), Inches(2.1), Inches(7.3), 19,
        )
        self.text(s, Inches(5.4), Inches(5.6), Inches(7.3), Inches(1.0), "Limit: scripted models and recorded responses. This does not prove real-world accuracy.", 17, True, INK)
        self.footer(s)

        # 13 evaluation / results
        cc = f["case_counts"]
        s = self.slide(
            f"The evaluation set is {cc['total']} labelled claims in {len(cc['by_lang'])} languages. Each case scores pass, abstain, fail (confidently wrong) or error. "
            + ("Read the numbers as they are; do not round them up." if self.res else "State plainly that the evaluation has not been run yet. We will not show a number we have not measured.")
        )
        self.title(s, f"Evaluation: {cc['total']} labelled claims in {len(cc['by_lang'])} languages", "Results")
        if self.res:
            ov = self.res["summary"]["overall"]
            tiles = [("Pass", ov["pass"]), ("Abstain", ov["abstain"]), ("Fail", ov["fail"]), ("Error", ov["error"])]
            for i, (lab, val) in enumerate(tiles):
                x = MX + i * Inches(2.0)
                self.text(s, x, Inches(2.1), Inches(1.9), Inches(1.2), str(val), 60, True, BLUE if lab == "Pass" else INK)
                self.text(s, x, Inches(3.3), Inches(1.9), Inches(0.4), lab, 16, False, SEC)
            acc = "n/a" if ov["accuracy"] is None else f"{ov['accuracy']:.0%}"
            self.text(s, MX, Inches(3.9), Inches(7.8), Inches(0.8), f"Accuracy {acc} over answered cases (errors excluded)", 22, True)
            fig = self.fig / "accuracy_by_language.png"
            if fig.exists():
                self.picture(s, fig, Inches(8.5), Inches(2.0), Inches(4.2), Inches(4.8))
            self.bullets(s, [f"{ov['fail']} confidently wrong verdicts: the costly outcome", f"{ov['abstain']} abstentions: unhelpful, not wrong"], MX, Inches(4.9), Inches(7.6), 18)
        else:
            shp = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, MX, Inches(2.2), Inches(7.6), Inches(2.6))
            shp.adjustments[0] = 0.05
            shp.fill.solid(); shp.fill.fore_color.rgb = RGBColor(0xEC, 0xEA, 0xE5); shp.line.color.rgb = SEC; shp.line.width = Pt(1.25); shp.shadow.inherit = False
            self.text(s, MX + Inches(0.25), Inches(2.4), Inches(7.1), Inches(0.6), "Results pending", 28, True, INK)
            self.text(s, MX + Inches(0.25), Inches(3.1), Inches(7.1), Inches(1.6), "The evaluation has not yet been run with a local model and live sources. No accuracy figure is claimed in this presentation.", 18, False, SEC)
            self.text(s, Inches(8.7), Inches(2.2), Inches(4), Inches(0.4), "What will be measured", 17, True, MUTED)
            self.bullets(s, ["Pass: verdict as expected", "Abstain: said unverifiable", "Fail: confidently wrong", "Error: request failed"], Inches(8.7), Inches(2.7), Inches(4), 18)
        self.text(s, MX, Inches(5.5), SW - 2 * MX, Inches(1.2), f"{cc['by_expect']['true']} true, {cc['by_expect']['false']} false and {cc['by_expect']['no_claims']} nothing-checkable cases. Facts are stable ones: capitals, landmarks, health myths. Non-English claims were AI-translated and need native-speaker review.", 16, False, SEC)
        self.footer(s)

        # 14 limitations + future
        s = self.slide("Be candid. The first limitation matters most: accuracy has not been measured. The rest are known gaps with a clear next step. Finish by naming what you would do next.")
        self.title(s, "What is not done yet, and what comes next", "Limitations and future work")
        self.text(s, MX, Inches(2.0), Inches(6), Inches(0.4), "Limitations", 18, True, MUTED)
        self.bullets(
            s,
            ["Accuracy not yet measured on real models and live sources", "Language ID cannot separate some languages that share a script", "English gloss comes from the extraction model, not a translator",
             "Government and fact-check sources use site-restricted search", "Credibility registry and thresholds are hand-set"],
            MX, Inches(2.5), Inches(6.0), 17,
        )
        self.text(s, Inches(7.1), Inches(2.0), Inches(5.5), Inches(0.4), "Next", 18, True, MUTED)
        self.bullets(
            s,
            ["Run the full evaluation; tune thresholds on held-out data", "Adopt IndicTrans2 and a wider language identifier", "Add first-party data (data.gov.in, Wikidata properties)", "Native-speaker review; cover every scheduled language", "Image and video claims"],
            Inches(7.1), Inches(2.5), Inches(5.6), 17,
        )
        self.footer(s)

        # 15 conclusion
        s = self.slide("Close with the three ideas and the honest status: built and tested, accuracy to be measured. Invite questions.")
        self.title(s, "A local, auditable fact-checker for Indian languages", "Conclusion")
        self.bullets(
            s,
            ["Seven agents, run entirely on local models", "Stances kept only when backed by a verifiable quote", "Verdict and confidence computed by rules; the model explains", "Weak languages flagged and capped, not hidden",
             f"{tf['passed']} tests pass; accuracy is the next thing to measure"],
            MX, Inches(2.2), Inches(11.5), 22, gap=0.22,
        )
        self.text(s, MX, Inches(6.0), SW - 2 * MX, Inches(0.6), "Thank you. Questions?", 28, True, BLUE)
        self.footer(s)

        # 16 references
        s = self.slide("Reference slide for questions. All entries were checked against the publisher or arXiv page.")
        self.title(s, "References", None)
        from refs import REFS

        cite = ["thorne2018", "augenstein2019", "gupta2021", "guo2022", "schlichtkrull2023", "singhal2021", "kazemi2021", "lewis2020", "yao2023", "gala2023", "chen2024", "yang2025"]
        short = []
        for i, k in enumerate(cite, 1):
            txt = REFS[k].replace("*", "")
            short.append(f"[{i}]  " + (txt if len(txt) < 150 else txt[:147] + "…"))
        self.bullets(s, [x for x in short[:6]], MX, Inches(1.7), Inches(5.9), 11, gap=0.07)
        self.bullets(s, [x for x in short[6:]], Inches(6.9), Inches(1.7), Inches(5.9), 11, gap=0.07)
        self.footer(s)


def build(out: Path, facts: dict, team: dict, results, fig_dir: Path) -> list[str]:
    d = Deck(facts, team, results, fig_dir)
    d.build()
    # app.xml can carry template 'Manager' / 'Company' values
    cp = d.prs.core_properties
    cp.author = cp.last_modified_by = cp.comments = cp.keywords = cp.subject = cp.title = ""
    d.prs.save(str(out))
    return d.missing
