"""References and a citation manager. Every entry was checked against its publisher/arXiv page in this
project (title, authors, venue, year). Numbering follows order of first citation, as IEEE requires.
"""

from __future__ import annotations

import re

REFS: dict[str, str] = {
    "thorne2018": 'J. Thorne, A. Vlachos, C. Christodoulopoulos, and A. Mittal, "FEVER: A large-scale dataset for fact extraction and VERification," in *Proc. NAACL-HLT*, New Orleans, LA, USA, 2018, pp. 809–819.',
    "augenstein2019": 'I. Augenstein *et al.*, "MultiFC: A real-world multi-domain dataset for evidence-based fact checking of claims," in *Proc. EMNLP-IJCNLP*, Hong Kong, China, 2019, pp. 4685–4697.',
    "gupta2021": 'A. Gupta and V. Srikumar, "X-FACT: A new benchmark dataset for multilingual fact checking," in *Proc. 59th Annu. Meeting ACL and 11th Int. Joint Conf. Natural Language Processing (Short Papers)*, 2021, pp. 675–682.',
    "guo2022": 'Z. Guo, M. Schlichtkrull, and A. Vlachos, "A survey on automated fact-checking," *Trans. Assoc. Comput. Linguistics*, vol. 10, pp. 178–206, 2022, doi: 10.1162/tacl_a_00454.',
    "schlichtkrull2023": 'M. Schlichtkrull, Z. Guo, and A. Vlachos, "AVeriTeC: A dataset for real-world claim verification with evidence from the web," in *Advances in Neural Information Processing Systems (Datasets and Benchmarks Track)*, vol. 36, 2023.',
    "singhal2021": 'S. Singhal, R. R. Shah, and P. Kumaraguru, "Factorization of fact-checks for low resource Indian languages," arXiv:2102.11276, 2021.',
    "kazemi2021": 'A. Kazemi, K. Garimella, D. Gaffney, and S. A. Hale, "Claim matching beyond English to scale global fact-checking," arXiv:2106.00853, 2021.',
    "lewis2020": 'P. Lewis *et al.*, "Retrieval-augmented generation for knowledge-intensive NLP tasks," in *Advances in Neural Information Processing Systems*, vol. 33, 2020, arXiv:2005.11401.',
    "yao2023": 'S. Yao *et al.*, "ReAct: Synergizing reasoning and acting in language models," in *Proc. Int. Conf. Learning Representations (ICLR)*, 2023, arXiv:2210.03629.',
    "gala2023": 'J. Gala *et al.*, "IndicTrans2: Towards high-quality and accessible machine translation models for all 22 scheduled Indian languages," *Trans. Mach. Learn. Res.*, 2023, arXiv:2305.16307.',
    "chen2024": 'J. Chen, S. Xiao, P. Zhang, K. Luo, D. Lian, and Z. Liu, "BGE M3-Embedding: Multi-lingual, multi-functionality, multi-granularity text embeddings through self-knowledge distillation," arXiv:2402.03216, 2024.',
    "yang2025": 'A. Yang *et al.*, "Qwen3 technical report," arXiv:2505.09388, 2025.',
    "gemma2025": 'Gemma Team, "Gemma 3 technical report," arXiv:2503.19786, 2025.',
    "googlefc": 'Google, "Fact Check Tools API," Google for Developers. [Online]. Available: https://developers.google.com/fact-check/tools/api (accessed Nov. 25, 2026).',
    "ollama": '"Ollama model library." [Online]. Available: https://ollama.com/library (accessed Nov. 25, 2026).',
}

_CITE = re.compile(r"\[@([a-z0-9_,;@ ]+)\]")


class Cite:
    """Assigns numbers in order of first citation and rewrites [@key] / [@a,@b] markers."""

    def __init__(self) -> None:
        self.order: list[str] = []

    def num(self, key: str) -> int:
        if key not in REFS:
            raise KeyError(f"Unknown reference key: {key}")
        if key not in self.order:
            self.order.append(key)
        return self.order.index(key) + 1

    def fmt(self, text: str) -> str:
        def sub(m: re.Match) -> str:
            keys = [k.strip().lstrip("@") for k in re.split(r"[,;]", m.group(1))]
            return ", ".join(f"[{self.num(k)}]" for k in keys)

        return _CITE.sub(sub, text)

    def entries(self) -> list[tuple[int, str]]:
        return [(i + 1, REFS[k]) for i, k in enumerate(self.order)]


# (key, short name, year, scope and size, headline finding, gap relative to this work)
LITERATURE: list[tuple[str, str, int, str, str, str]] = [
    ("thorne2018", "FEVER", 2018, "185,445 claims written from Wikipedia sentences; three-way labels with evidence sentences", "Pipeline baseline reaches 31.87% accuracy when correct evidence is also required", "English only; synthetic claims over a fixed Wikipedia corpus"),
    ("augenstein2019", "MultiFC", 2019, "34,918 real claims from 26 English fact-checking sites, with evidence pages and metadata", "Best model reaches 49.2% macro F1", "English only; a dataset and models, not a deployable retrieval system"),
    ("gupta2021", "X-FACT", 2021, "Short statements in 25 languages labelled by expert fact-checkers", "Best model reaches about 40% F-score", "Classification benchmark; no retrieval of evidence or source validation"),
    ("singhal2021", "FactDRIL", 2021, "22,435 samples crawled from 11 IFCN-certified Indian fact-checking websites", "Releases a data repository covering Hindi and regional languages", "A data resource; no verification pipeline"),
    ("kazemi2021", "Claim matching", 2021, "5,066 messages in English, Hindi, Bengali, Malayalam and Tamil annotated for claim-like statements", "Shows claim matching extends beyond English", "Matches claims to prior checks; does not verify new ones"),
    ("schlichtkrull2023", "AVeriTeC", 2023, "4,568 real-world claims from 50 fact-checking organisations, with question-answer evidence from the web", "Provides a baseline and scheme for open-web verification", "English; benchmark rather than a multilingual system"),
    ("lewis2020", "RAG", 2020, "Pairs a generator with a dense index of Wikipedia", "State of the art on three open-domain QA tasks at the time", "General QA method; no source credibility or verdict policy"),
    ("yao2023", "ReAct", 2023, "Interleaves reasoning steps with actions such as querying Wikipedia", "Tested on HotpotQA, FEVER, ALFWorld and WebShop", "Relies on one model's judgement; not tied to Indian languages"),
]
